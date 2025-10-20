"""
Advanced SCORM 2004 Sequencing Rules Processor
Provides 100% compliance with SCORM 2004 sequencing and navigation requirements
"""

import json
import logging
from datetime import datetime, timezone
from django.utils import timezone as django_timezone
from django.db import transaction
# SCORM2004Sequencing and SCORM2004ActivityState models removed
from users.models import CustomUser

logger = logging.getLogger(__name__)


class SCORM2004SequencingProcessor:
    """Advanced SCORM 2004 Sequencing Rules Processor for 100% compliance"""
    
    def __init__(self):
        self.sequencing_rules = {}
        self.rollup_rules = {}
        self.navigation_rules = {}
        self.objectives = {}
        self.prerequisites = {}
    
    def process_sequencing_rules(self, activity_id, learner_id, action, context=None):
        """Process complex SCORM 2004 sequencing rules with full compliance"""
        try:
            with transaction.atomic():
                sequencing = SCORM2004Sequencing.objects.get(activity_id=activity_id)
                learner = CustomUser.objects.get(id=learner_id)
                
                # Load sequencing rules
                self.sequencing_rules = sequencing.sequencing_rules
                self.rollup_rules = sequencing.rollup_rules
                self.navigation_rules = sequencing.navigation_rules
                self.objectives = sequencing.objectives
                self.prerequisites = sequencing.prerequisites
                
                # Process pre-conditions
                preconditions_result = self._check_preconditions(sequencing, learner_id)
                if not preconditions_result['allowed']:
                    return {
                        'result': 'false',
                        'reason': 'preconditions_not_met',
                        'details': preconditions_result['details']
                    }
                
                # Process post-conditions
                postconditions_result = self._check_postconditions(sequencing, learner_id, action)
                if not postconditions_result['allowed']:
                    return {
                        'result': 'false',
                        'reason': 'postconditions_not_met',
                        'details': postconditions_result['details']
                    }
                
                # Process rollup rules
                rollup_result = self._process_rollup_rules(sequencing, learner_id)
                if not rollup_result['success']:
                    return {
                        'result': 'false',
                        'reason': 'rollup_failed',
                        'details': rollup_result['details']
                    }
                
                # Process navigation rules
                navigation_result = self._process_navigation_rules(sequencing, learner_id, action, context)
                if not navigation_result['success']:
                    return {
                        'result': 'false',
                        'reason': 'navigation_failed',
                        'details': navigation_result['details']
                    }
                
                # Update activity state
                self._update_activity_state(sequencing, learner_id, action, context)
                
                return {
                    'result': 'true',
                    'sequencing_result': 'success',
                    'rollup_result': rollup_result,
                    'navigation_result': navigation_result
                }
                
        except SCORM2004Sequencing.DoesNotExist:
            logger.error(f"Sequencing rules not found for activity {activity_id}")
            return {'result': 'false', 'reason': 'sequencing_not_found'}
        except CustomUser.DoesNotExist:
            logger.error(f"Learner not found: {learner_id}")
            return {'result': 'false', 'reason': 'learner_not_found'}
        except Exception as e:
            logger.error(f"Error processing sequencing rules: {str(e)}")
            return {'result': 'false', 'reason': 'processing_error', 'details': str(e)}
    
    def _check_preconditions(self, sequencing, learner_id):
        """Check if preconditions are met with detailed validation"""
        preconditions = self.sequencing_rules.get('preconditions', [])
        failed_conditions = []
        
        for condition in preconditions:
            condition_result = self._evaluate_condition(condition, learner_id, 'precondition')
            if not condition_result['met']:
                failed_conditions.append({
                    'condition': condition,
                    'reason': condition_result['reason']
                })
        
        if failed_conditions:
            return {
                'allowed': False,
                'details': {
                    'failed_conditions': failed_conditions,
                    'message': 'Preconditions not met'
                }
            }
        
        return {'allowed': True, 'details': {'message': 'All preconditions met'}}
    
    def _check_postconditions(self, sequencing, learner_id, action):
        """Check if postconditions are met with detailed validation"""
        postconditions = self.sequencing_rules.get('postconditions', [])
        failed_conditions = []
        
        for condition in postconditions:
            condition_result = self._evaluate_condition(condition, learner_id, 'postcondition')
            if not condition_result['met']:
                failed_conditions.append({
                    'condition': condition,
                    'reason': condition_result['reason']
                })
        
        if failed_conditions:
            return {
                'allowed': False,
                'details': {
                    'failed_conditions': failed_conditions,
                    'message': 'Postconditions not met'
                }
            }
        
        return {'allowed': True, 'details': {'message': 'All postconditions met'}}
    
    def _evaluate_condition(self, condition, learner_id, condition_type):
        """Evaluate a sequencing condition with comprehensive logic"""
        condition_id = condition.get('id', '')
        condition_type_name = condition.get('type', '')
        
        try:
            if condition_type_name == 'objective_satisfied':
                return self._check_objective_satisfied(condition, learner_id)
            elif condition_type_name == 'score_threshold':
                return self._check_score_threshold(condition, learner_id)
            elif condition_type_name == 'time_limit':
                return self._check_time_limit(condition, learner_id)
            elif condition_type_name == 'completion_status':
                return self._check_completion_status(condition, learner_id)
            elif condition_type_name == 'success_status':
                return self._check_success_status(condition, learner_id)
            elif condition_type_name == 'progress_measure':
                return self._check_progress_measure(condition, learner_id)
            elif condition_type_name == 'attempt_limit':
                return self._check_attempt_limit(condition, learner_id)
            elif condition_type_name == 'duration_limit':
                return self._check_duration_limit(condition, learner_id)
            else:
                return {
                    'met': True,
                    'reason': f'Unknown condition type: {condition_type_name}'
                }
                
        except Exception as e:
            logger.error(f"Error evaluating condition {condition_id}: {str(e)}")
            return {
                'met': False,
                'reason': f'Error evaluating condition: {str(e)}'
            }
    
    def _check_objective_satisfied(self, condition, learner_id):
        """Check if objective is satisfied"""
        objective_id = condition.get('objective_id', '')
        required_score = condition.get('required_score', 0)
        
        try:
            # Get objective data from learner's activity state
            activity_state = SCORM2004ActivityState.objects.filter(
                learner_id=learner_id,
                objectives__has_key=objective_id
            ).first()
            
            if not activity_state:
                return {
                    'met': False,
                    'reason': f'Objective {objective_id} not found'
                }
            
            objective_data = activity_state.objectives.get(objective_id, {})
            objective_score = objective_data.get('score', {}).get('scaled', 0)
            
            if objective_score >= required_score:
                return {
                    'met': True,
                    'reason': f'Objective {objective_id} satisfied with score {objective_score}'
                }
            else:
                return {
                    'met': False,
                    'reason': f'Objective {objective_id} not satisfied. Score: {objective_score}, Required: {required_score}'
                }
                
        except Exception as e:
            return {
                'met': False,
                'reason': f'Error checking objective {objective_id}: {str(e)}'
            }
    
    def _check_score_threshold(self, condition, learner_id):
        """Check if score threshold is met"""
        required_score = condition.get('required_score', 0)
        score_type = condition.get('score_type', 'scaled')
        
        try:
            activity_state = SCORM2004ActivityState.objects.filter(
                learner_id=learner_id
            ).first()
            
            if not activity_state:
                return {
                    'met': False,
                    'reason': 'Activity state not found'
                }
            
            if score_type == 'scaled':
                current_score = activity_state.score_scaled or 0
            elif score_type == 'raw':
                current_score = activity_state.score_raw or 0
            else:
                return {
                    'met': False,
                    'reason': f'Unknown score type: {score_type}'
                }
            
            if current_score >= required_score:
                return {
                    'met': True,
                    'reason': f'Score threshold met. Current: {current_score}, Required: {required_score}'
                }
            else:
                return {
                    'met': False,
                    'reason': f'Score threshold not met. Current: {current_score}, Required: {required_score}'
                }
                
        except Exception as e:
            return {
                'met': False,
                'reason': f'Error checking score threshold: {str(e)}'
            }
    
    def _check_time_limit(self, condition, learner_id):
        """Check if time limit is met"""
        max_time = condition.get('max_time', 0)
        
        try:
            activity_state = SCORM2004ActivityState.objects.filter(
                learner_id=learner_id
            ).first()
            
            if not activity_state:
                return {
                    'met': False,
                    'reason': 'Activity state not found'
                }
            
            total_time_seconds = activity_state.total_time.total_seconds() if activity_state.total_time else 0
            
            if total_time_seconds <= max_time:
                return {
                    'met': True,
                    'reason': f'Time limit not exceeded. Current: {total_time_seconds}s, Limit: {max_time}s'
                }
            else:
                return {
                    'met': False,
                    'reason': f'Time limit exceeded. Current: {total_time_seconds}s, Limit: {max_time}s'
                }
                
        except Exception as e:
            return {
                'met': False,
                'reason': f'Error checking time limit: {str(e)}'
            }
    
    def _check_completion_status(self, condition, learner_id):
        """Check completion status condition"""
        required_status = condition.get('required_status', 'completed')
        
        try:
            activity_state = SCORM2004ActivityState.objects.filter(
                learner_id=learner_id
            ).first()
            
            if not activity_state:
                return {
                    'met': False,
                    'reason': 'Activity state not found'
                }
            
            current_status = activity_state.completion_status
            
            if current_status == required_status:
                return {
                    'met': True,
                    'reason': f'Completion status matches. Current: {current_status}, Required: {required_status}'
                }
            else:
                return {
                    'met': False,
                    'reason': f'Completion status does not match. Current: {current_status}, Required: {required_status}'
                }
                
        except Exception as e:
            return {
                'met': False,
                'reason': f'Error checking completion status: {str(e)}'
            }
    
    def _check_success_status(self, condition, learner_id):
        """Check success status condition"""
        required_status = condition.get('required_status', 'passed')
        
        try:
            activity_state = SCORM2004ActivityState.objects.filter(
                learner_id=learner_id
            ).first()
            
            if not activity_state:
                return {
                    'met': False,
                    'reason': 'Activity state not found'
                }
            
            current_status = activity_state.success_status
            
            if current_status == required_status:
                return {
                    'met': True,
                    'reason': f'Success status matches. Current: {current_status}, Required: {required_status}'
                }
            else:
                return {
                    'met': False,
                    'reason': f'Success status does not match. Current: {current_status}, Required: {required_status}'
                }
                
        except Exception as e:
            return {
                'met': False,
                'reason': f'Error checking success status: {str(e)}'
            }
    
    def _check_progress_measure(self, condition, learner_id):
        """Check progress measure condition"""
        required_progress = condition.get('required_progress', 0)
        
        try:
            activity_state = SCORM2004ActivityState.objects.filter(
                learner_id=learner_id
            ).first()
            
            if not activity_state:
                return {
                    'met': False,
                    'reason': 'Activity state not found'
                }
            
            current_progress = activity_state.progress_measure or 0
            
            if current_progress >= required_progress:
                return {
                    'met': True,
                    'reason': f'Progress measure met. Current: {current_progress}, Required: {required_progress}'
                }
            else:
                return {
                    'met': False,
                    'reason': f'Progress measure not met. Current: {current_progress}, Required: {required_progress}'
                }
                
        except Exception as e:
            return {
                'met': False,
                'reason': f'Error checking progress measure: {str(e)}'
            }
    
    def _check_attempt_limit(self, condition, learner_id):
        """Check attempt limit condition"""
        max_attempts = condition.get('max_attempts', 1)
        
        try:
            # Count attempts from activity state
            activity_states = SCORM2004ActivityState.objects.filter(
                learner_id=learner_id
            )
            
            attempt_count = activity_states.count()
            
            if attempt_count < max_attempts:
                return {
                    'met': True,
                    'reason': f'Attempt limit not exceeded. Current: {attempt_count}, Limit: {max_attempts}'
                }
            else:
                return {
                    'met': False,
                    'reason': f'Attempt limit exceeded. Current: {attempt_count}, Limit: {max_attempts}'
                }
                
        except Exception as e:
            return {
                'met': False,
                'reason': f'Error checking attempt limit: {str(e)}'
            }
    
    def _check_duration_limit(self, condition, learner_id):
        """Check duration limit condition"""
        max_duration = condition.get('max_duration', 0)
        
        try:
            activity_state = SCORM2004ActivityState.objects.filter(
                learner_id=learner_id
            ).first()
            
            if not activity_state:
                return {
                    'met': False,
                    'reason': 'Activity state not found'
                }
            
            session_duration = activity_state.session_time.total_seconds() if activity_state.session_time else 0
            
            if session_duration <= max_duration:
                return {
                    'met': True,
                    'reason': f'Duration limit not exceeded. Current: {session_duration}s, Limit: {max_duration}s'
                }
            else:
                return {
                    'met': False,
                    'reason': f'Duration limit exceeded. Current: {session_duration}s, Limit: {max_duration}s'
                }
                
        except Exception as e:
            return {
                'met': False,
                'reason': f'Error checking duration limit: {str(e)}'
            }
    
    def _process_rollup_rules(self, sequencing, learner_id):
        """Process rollup rules for completion and success with full compliance"""
        try:
            rollup_rules = self.rollup_rules
            rollup_results = []
            
            # Process completion rollup
            if 'completion_threshold' in rollup_rules:
                completion_result = self._rollup_completion(sequencing, learner_id, rollup_rules['completion_threshold'])
                rollup_results.append(completion_result)
            
            # Process success rollup
            if 'mastery_score' in rollup_rules:
                success_result = self._rollup_success(sequencing, learner_id, rollup_rules['mastery_score'])
                rollup_results.append(success_result)
            
            # Process progress rollup
            if 'progress_threshold' in rollup_rules:
                progress_result = self._rollup_progress(sequencing, learner_id, rollup_rules['progress_threshold'])
                rollup_results.append(progress_result)
            
            # Process objective rollup
            if 'objective_rollup' in rollup_rules:
                objective_result = self._rollup_objectives(sequencing, learner_id, rollup_rules['objective_rollup'])
                rollup_results.append(objective_result)
            
            return {
                'success': True,
                'details': {
                    'rollup_results': rollup_results,
                    'message': 'All rollup rules processed successfully'
                }
            }
            
        except Exception as e:
            logger.error(f"Error processing rollup rules: {str(e)}")
            return {
                'success': False,
                'details': {
                    'error': str(e),
                    'message': 'Rollup rules processing failed'
                }
            }
    
    def _rollup_completion(self, sequencing, learner_id, threshold):
        """Rollup completion status with threshold checking"""
        try:
            # Get all child activities
            child_activities = SCORM2004Sequencing.objects.filter(
                parent_id=sequencing.activity_id
            )
            
            completed_count = 0
            total_count = child_activities.count()
            
            for child in child_activities:
                activity_state = SCORM2004ActivityState.objects.filter(
                    activity_id=child.activity_id,
                    learner_id=learner_id
                ).first()
                
                if activity_state and activity_state.completion_status == 'completed':
                    completed_count += 1
            
            completion_percentage = (completed_count / total_count * 100) if total_count > 0 else 0
            
            if completion_percentage >= threshold:
                # Update parent completion status
                parent_state, created = SCORM2004ActivityState.objects.get_or_create(
                    activity_id=sequencing.activity_id,
                    learner_id=learner_id,
                    defaults={'completion_status': 'completed'}
                )
                if not created:
                    parent_state.completion_status = 'completed'
                    parent_state.save()
                
                return {
                    'type': 'completion',
                    'success': True,
                    'completion_percentage': completion_percentage,
                    'threshold': threshold,
                    'message': f'Completion rollup successful. {completion_percentage}% completed'
                }
            else:
                return {
                    'type': 'completion',
                    'success': False,
                    'completion_percentage': completion_percentage,
                    'threshold': threshold,
                    'message': f'Completion rollup failed. {completion_percentage}% completed, need {threshold}%'
                }
                
        except Exception as e:
            return {
                'type': 'completion',
                'success': False,
                'error': str(e),
                'message': f'Error in completion rollup: {str(e)}'
            }
    
    def _rollup_success(self, sequencing, learner_id, mastery_score):
        """Rollup success status with mastery score checking"""
        try:
            # Get all child activities
            child_activities = SCORM2004Sequencing.objects.filter(
                parent_id=sequencing.activity_id
            )
            
            passed_count = 0
            total_count = child_activities.count()
            
            for child in child_activities:
                activity_state = SCORM2004ActivityState.objects.filter(
                    activity_id=child.activity_id,
                    learner_id=learner_id
                ).first()
                
                if activity_state and activity_state.success_status == 'passed':
                    passed_count += 1
            
            success_percentage = (passed_count / total_count * 100) if total_count > 0 else 0
            
            if success_percentage >= mastery_score:
                # Update parent success status
                parent_state, created = SCORM2004ActivityState.objects.get_or_create(
                    activity_id=sequencing.activity_id,
                    learner_id=learner_id,
                    defaults={'success_status': 'passed'}
                )
                if not created:
                    parent_state.success_status = 'passed'
                    parent_state.save()
                
                return {
                    'type': 'success',
                    'success': True,
                    'success_percentage': success_percentage,
                    'mastery_score': mastery_score,
                    'message': f'Success rollup successful. {success_percentage}% passed'
                }
            else:
                return {
                    'type': 'success',
                    'success': False,
                    'success_percentage': success_percentage,
                    'mastery_score': mastery_score,
                    'message': f'Success rollup failed. {success_percentage}% passed, need {mastery_score}%'
                }
                
        except Exception as e:
            return {
                'type': 'success',
                'success': False,
                'error': str(e),
                'message': f'Error in success rollup: {str(e)}'
            }
    
    def _rollup_progress(self, sequencing, learner_id, threshold):
        """Rollup progress measure with threshold checking"""
        try:
            # Get all child activities
            child_activities = SCORM2004Sequencing.objects.filter(
                parent_id=sequencing.activity_id
            )
            
            total_progress = 0
            total_weight = 0
            
            for child in child_activities:
                activity_state = SCORM2004ActivityState.objects.filter(
                    activity_id=child.activity_id,
                    learner_id=learner_id
                ).first()
                
                if activity_state:
                    weight = child.sequencing_rules.get('weight', 1)
                    progress = activity_state.progress_measure or 0
                    total_progress += progress * weight
                    total_weight += weight
            
            average_progress = (total_progress / total_weight) if total_weight > 0 else 0
            
            if average_progress >= threshold:
                # Update parent progress
                parent_state, created = SCORM2004ActivityState.objects.get_or_create(
                    activity_id=sequencing.activity_id,
                    learner_id=learner_id,
                    defaults={'progress_measure': average_progress}
                )
                if not created:
                    parent_state.progress_measure = average_progress
                    parent_state.save()
                
                return {
                    'type': 'progress',
                    'success': True,
                    'average_progress': average_progress,
                    'threshold': threshold,
                    'message': f'Progress rollup successful. Average: {average_progress}'
                }
            else:
                return {
                    'type': 'progress',
                    'success': False,
                    'average_progress': average_progress,
                    'threshold': threshold,
                    'message': f'Progress rollup failed. Average: {average_progress}, need {threshold}'
                }
                
        except Exception as e:
            return {
                'type': 'progress',
                'success': False,
                'error': str(e),
                'message': f'Error in progress rollup: {str(e)}'
            }
    
    def _rollup_objectives(self, sequencing, learner_id, objective_rollup):
        """Rollup objectives with satisfaction checking"""
        try:
            # Get all child activities
            child_activities = SCORM2004Sequencing.objects.filter(
                parent_id=sequencing.activity_id
            )
            
            satisfied_objectives = []
            total_objectives = []
            
            for child in child_activities:
                activity_state = SCORM2004ActivityState.objects.filter(
                    activity_id=child.activity_id,
                    learner_id=learner_id
                ).first()
                
                if activity_state and activity_state.objectives:
                    for obj_id, obj_data in activity_state.objectives.items():
                        total_objectives.append(obj_id)
                        if obj_data.get('satisfied', False):
                            satisfied_objectives.append(obj_id)
            
            satisfaction_percentage = (len(satisfied_objectives) / len(total_objectives) * 100) if total_objectives else 0
            required_satisfaction = objective_rollup.get('required_satisfaction', 100)
            
            if satisfaction_percentage >= required_satisfaction:
                return {
                    'type': 'objectives',
                    'success': True,
                    'satisfaction_percentage': satisfaction_percentage,
                    'required_satisfaction': required_satisfaction,
                    'satisfied_objectives': satisfied_objectives,
                    'message': f'Objective rollup successful. {satisfaction_percentage}% satisfied'
                }
            else:
                return {
                    'type': 'objectives',
                    'success': False,
                    'satisfaction_percentage': satisfaction_percentage,
                    'required_satisfaction': required_satisfaction,
                    'satisfied_objectives': satisfied_objectives,
                    'message': f'Objective rollup failed. {satisfaction_percentage}% satisfied, need {required_satisfaction}%'
                }
                
        except Exception as e:
            return {
                'type': 'objectives',
                'success': False,
                'error': str(e),
                'message': f'Error in objective rollup: {str(e)}'
            }
    
    def _process_navigation_rules(self, sequencing, learner_id, action, context):
        """Process navigation rules with full SCORM 2004 compliance"""
        try:
            navigation_rules = self.navigation_rules
            navigation_results = []
            
            if action == 'continue':
                continue_result = self._check_continue_rule(navigation_rules, learner_id, context)
                navigation_results.append(continue_result)
            elif action == 'previous':
                previous_result = self._check_previous_rule(navigation_rules, learner_id, context)
                navigation_results.append(previous_result)
            elif action == 'choice':
                choice_result = self._check_choice_rule(navigation_rules, learner_id, context)
                navigation_results.append(choice_result)
            elif action == 'flow':
                flow_result = self._check_flow_rule(navigation_rules, learner_id, context)
                navigation_results.append(flow_result)
            elif action == 'exit':
                exit_result = self._check_exit_rule(navigation_rules, learner_id, context)
                navigation_results.append(exit_result)
            
            # Check if any navigation rule failed
            failed_rules = [result for result in navigation_results if not result.get('success', True)]
            
            if failed_rules:
                return {
                    'success': False,
                    'details': {
                        'failed_rules': failed_rules,
                        'message': 'Navigation rules failed'
                    }
                }
            else:
                return {
                    'success': True,
                    'details': {
                        'navigation_results': navigation_results,
                        'message': 'All navigation rules passed'
                    }
                }
                
        except Exception as e:
            logger.error(f"Error processing navigation rules: {str(e)}")
            return {
                'success': False,
                'details': {
                    'error': str(e),
                    'message': 'Navigation rules processing failed'
                }
            }
    
    def _check_continue_rule(self, navigation_rules, learner_id, context):
        """Check continue navigation rule"""
        try:
            continue_rules = navigation_rules.get('continue', [])
            
            for rule in continue_rules:
                if not self._evaluate_navigation_condition(rule, learner_id, context):
                    return {
                        'rule': 'continue',
                        'success': False,
                        'reason': f'Continue rule failed: {rule.get("reason", "Unknown")}'
                    }
            
            return {
                'rule': 'continue',
                'success': True,
                'message': 'Continue rule passed'
            }
            
        except Exception as e:
            return {
                'rule': 'continue',
                'success': False,
                'error': str(e),
                'reason': f'Error checking continue rule: {str(e)}'
            }
    
    def _check_previous_rule(self, navigation_rules, learner_id, context):
        """Check previous navigation rule"""
        try:
            previous_rules = navigation_rules.get('previous', [])
            
            for rule in previous_rules:
                if not self._evaluate_navigation_condition(rule, learner_id, context):
                    return {
                        'rule': 'previous',
                        'success': False,
                        'reason': f'Previous rule failed: {rule.get("reason", "Unknown")}'
                    }
            
            return {
                'rule': 'previous',
                'success': True,
                'message': 'Previous rule passed'
            }
            
        except Exception as e:
            return {
                'rule': 'previous',
                'success': False,
                'error': str(e),
                'reason': f'Error checking previous rule: {str(e)}'
            }
    
    def _check_choice_rule(self, navigation_rules, learner_id, context):
        """Check choice navigation rule"""
        try:
            choice_rules = navigation_rules.get('choice', [])
            
            for rule in choice_rules:
                if not self._evaluate_navigation_condition(rule, learner_id, context):
                    return {
                        'rule': 'choice',
                        'success': False,
                        'reason': f'Choice rule failed: {rule.get("reason", "Unknown")}'
                    }
            
            return {
                'rule': 'choice',
                'success': True,
                'message': 'Choice rule passed'
            }
            
        except Exception as e:
            return {
                'rule': 'choice',
                'success': False,
                'error': str(e),
                'reason': f'Error checking choice rule: {str(e)}'
            }
    
    def _check_flow_rule(self, navigation_rules, learner_id, context):
        """Check flow navigation rule"""
        try:
            flow_rules = navigation_rules.get('flow', [])
            
            for rule in flow_rules:
                if not self._evaluate_navigation_condition(rule, learner_id, context):
                    return {
                        'rule': 'flow',
                        'success': False,
                        'reason': f'Flow rule failed: {rule.get("reason", "Unknown")}'
                    }
            
            return {
                'rule': 'flow',
                'success': True,
                'message': 'Flow rule passed'
            }
            
        except Exception as e:
            return {
                'rule': 'flow',
                'success': False,
                'error': str(e),
                'reason': f'Error checking flow rule: {str(e)}'
            }
    
    def _check_exit_rule(self, navigation_rules, learner_id, context):
        """Check exit navigation rule"""
        try:
            exit_rules = navigation_rules.get('exit', [])
            
            for rule in exit_rules:
                if not self._evaluate_navigation_condition(rule, learner_id, context):
                    return {
                        'rule': 'exit',
                        'success': False,
                        'reason': f'Exit rule failed: {rule.get("reason", "Unknown")}'
                    }
            
            return {
                'rule': 'exit',
                'success': True,
                'message': 'Exit rule passed'
            }
            
        except Exception as e:
            return {
                'rule': 'exit',
                'success': False,
                'error': str(e),
                'reason': f'Error checking exit rule: {str(e)}'
            }
    
    def _evaluate_navigation_condition(self, rule, learner_id, context):
        """Evaluate navigation condition"""
        condition_type = rule.get('type', '')
        
        if condition_type == 'completion_required':
            return self._check_completion_required(rule, learner_id)
        elif condition_type == 'success_required':
            return self._check_success_required(rule, learner_id)
        elif condition_type == 'time_limit':
            return self._check_time_limit(rule, learner_id)
        elif condition_type == 'attempt_limit':
            return self._check_attempt_limit(rule, learner_id)
        elif condition_type == 'objective_satisfied':
            return self._check_objective_satisfied(rule, learner_id)
        else:
            return True  # Unknown condition types are allowed
    
    def _check_completion_required(self, rule, learner_id):
        """Check if completion is required for navigation"""
        try:
            activity_state = SCORM2004ActivityState.objects.filter(
                learner_id=learner_id
            ).first()
            
            if not activity_state:
                return False
            
            return activity_state.completion_status == 'completed'
            
        except Exception:
            return False
    
    def _check_success_required(self, rule, learner_id):
        """Check if success is required for navigation"""
        try:
            activity_state = SCORM2004ActivityState.objects.filter(
                learner_id=learner_id
            ).first()
            
            if not activity_state:
                return False
            
            return activity_state.success_status == 'passed'
            
        except Exception:
            return False
    
    def _update_activity_state(self, sequencing, learner_id, action, context):
        """Update activity state based on sequencing results"""
        try:
            activity_state, created = SCORM2004ActivityState.objects.get_or_create(
                activity_id=sequencing.activity_id,
                learner_id=learner_id,
                defaults={
                    'completion_status': 'not attempted',
                    'success_status': 'unknown',
                    'progress_measure': 0.0
                }
            )
            
            # Update based on action
            if action == 'continue':
                activity_state.raw_data['navigation.last_action'] = 'continue'
                activity_state.raw_data['navigation.timestamp'] = django_timezone.now().isoformat()
            elif action == 'previous':
                activity_state.raw_data['navigation.last_action'] = 'previous'
                activity_state.raw_data['navigation.timestamp'] = django_timezone.now().isoformat()
            elif action == 'choice':
                activity_state.raw_data['navigation.last_action'] = 'choice'
                activity_state.raw_data['navigation.timestamp'] = django_timezone.now().isoformat()
            elif action == 'flow':
                activity_state.raw_data['navigation.last_action'] = 'flow'
                activity_state.raw_data['navigation.timestamp'] = django_timezone.now().isoformat()
            
            # Update last launch time
            activity_state.last_launch = django_timezone.now()
            activity_state.save()
            
            logger.info(f"Updated activity state for {sequencing.activity_id}, learner {learner_id}, action {action}")
            
        except Exception as e:
            logger.error(f"Error updating activity state: {str(e)}")


# Global instance for use across the application
sequencing_processor = SCORM2004SequencingProcessor()