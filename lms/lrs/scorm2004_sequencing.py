"""
SCORM 2004 Sequencing Implementation
Provides complete SCORM 2004 sequencing and navigation support
"""

import json
from datetime import datetime, timezone
from django.utils import timezone as django_timezone
from django.db import transaction
from .models import SCORM2004Sequencing, SCORM2004ActivityState


class SCORM2004SequencingEngine:
    """SCORM 2004 Sequencing Engine"""
    
    def __init__(self, activity_id, learner, registration_id):
        self.activity_id = activity_id
        self.learner = learner
        self.registration_id = registration_id
        self.sequencing = None
        self.activity_state = None
        self._load_sequencing_data()
    
    def _load_sequencing_data(self):
        """Load sequencing rules and activity state"""
        try:
            self.sequencing = SCORM2004Sequencing.objects.get(activity_id=self.activity_id)
            self.activity_state, created = SCORM2004ActivityState.objects.get_or_create(
                activity_id=self.activity_id,
                learner=self.learner,
                registration_id=self.registration_id
            )
        except SCORM2004Sequencing.DoesNotExist:
            # Create default sequencing if not exists
            self.sequencing = SCORM2004Sequencing.objects.create(
                activity_id=self.activity_id,
                title=f"Activity {self.activity_id}",
                sequencing_rules={},
                rollup_rules={},
                navigation_rules={},
                objectives={},
                prerequisites={}
            )
            self.activity_state, created = SCORM2004ActivityState.objects.get_or_create(
                activity_id=self.activity_id,
                learner=self.learner,
                registration_id=self.registration_id
            )
    
    def process_sequencing_rules(self, action, target=None):
        """Process SCORM 2004 sequencing rules with enhanced error handling"""
        try:
            sequencing_rules = self.sequencing.sequencing_rules or {}
            
            # Validate input parameters
            if not self._validate_input(action, target):
                return False, "Invalid input parameters"
            
            # Pre-conditions
            pre_condition_result, pre_condition_message = self._check_pre_conditions(action, target)
            if not pre_condition_result:
                return False, f"Pre-conditions not met: {pre_condition_message}"
            
            # Post-conditions
            post_condition_result, post_condition_message = self._check_post_conditions(action, target)
            if not post_condition_result:
                return False, f"Post-conditions not met: {post_condition_message}"
            
            # Apply sequencing rules
            result = self._apply_sequencing_rules(action, target)
            
            # Update activity state
            self._update_activity_state(action, target)
            
            return True, result
            
        except Exception as e:
            # Log error and return safe response
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error processing sequencing rules: {e}")
            return False, f"Sequencing error: {str(e)}"
    
    def _validate_input(self, action, target):
        """Validate input parameters"""
        # Validate action
        valid_actions = ['navigate', 'rollup', 'choice', 'flow', 'completed', 'passed', 'failed']
        if action not in valid_actions:
            return False
        
        # Validate target if provided
        if target and not isinstance(target, str):
            return False
        
        return True
    
    def _check_pre_conditions(self, action, target):
        """Check pre-conditions for sequencing"""
        try:
            pre_conditions = self.sequencing.sequencing_rules.get('pre_conditions', {})
            
            # Check if activity is available
            if not self._is_activity_available():
                return False, "Activity not available"
            
            # Check prerequisites
            prereq_result, prereq_message = self._check_prerequisites()
            if not prereq_result:
                return False, f"Prerequisites not met: {prereq_message}"
            
            # Check objective satisfaction
            objective_result, objective_message = self._check_objective_satisfaction()
            if not objective_result:
                return False, f"Objectives not satisfied: {objective_message}"
            
            return True, "Pre-conditions satisfied"
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error checking pre-conditions: {e}")
            return False, f"Pre-condition error: {str(e)}"
    
    def _check_post_conditions(self, action, target):
        """Check post-conditions for sequencing"""
        try:
            post_conditions = self.sequencing.sequencing_rules.get('post_conditions', {})
            
            # Check if action is allowed
            allowed_actions = post_conditions.get('allowed_actions', [])
            if allowed_actions and action not in allowed_actions:
                return False, f"Action '{action}' not allowed"
            
            # Check if target is valid
            if target and 'valid_targets' in post_conditions:
                valid_targets = post_conditions['valid_targets']
                if target not in valid_targets:
                    return False, f"Target '{target}' not valid"
            
            return True, "Post-conditions satisfied"
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error checking post-conditions: {e}")
            return False, f"Post-condition error: {str(e)}"
    
    def _apply_sequencing_rules(self, action, target):
        """Apply sequencing rules based on action"""
        sequencing_rules = self.sequencing.sequencing_rules or {}
        
        if action == 'navigate':
            return self._handle_navigation(target)
        elif action == 'rollup':
            return self._handle_rollup()
        elif action == 'choice':
            return self._handle_choice(target)
        elif action == 'flow':
            return self._handle_flow()
        else:
            return self._handle_default(action)
    
    def _handle_navigation(self, target):
        """Handle navigation sequencing"""
        navigation_rules = self.sequencing.navigation_rules or {}
        
        # Check navigation rules
        if 'forward_only' in navigation_rules and navigation_rules['forward_only']:
            # Only allow forward navigation
            if target and self._is_forward_navigation(target):
                return self._navigate_to_target(target)
        
        # Check choice navigation
        if 'choice' in navigation_rules and navigation_rules['choice']:
            return self._navigate_to_target(target)
        
        # Check flow navigation
        if 'flow' in navigation_rules and navigation_rules['flow']:
            return self._navigate_flow(target)
        
        return self._navigate_to_target(target)
    
    def _handle_rollup(self):
        """Handle rollup sequencing"""
        rollup_rules = self.sequencing.rollup_rules or {}
        
        # Check completion rollup
        if 'completion_rollup' in rollup_rules:
            self._rollup_completion()
        
        # Check objective rollup
        if 'objective_rollup' in rollup_rules:
            self._rollup_objectives()
        
        # Check progress rollup
        if 'progress_rollup' in rollup_rules:
            self._rollup_progress()
        
        return "Rollup completed"
    
    def _handle_choice(self, target):
        """Handle choice sequencing"""
        choice_rules = self.sequencing.sequencing_rules.get('choice', {})
        
        if choice_rules.get('enabled', True):
            return self._navigate_to_target(target)
        else:
            return "Choice navigation not allowed"
    
    def _handle_flow(self):
        """Handle flow sequencing"""
        flow_rules = self.sequencing.sequencing_rules.get('flow', {})
        
        if flow_rules.get('enabled', True):
            return self._navigate_flow()
        else:
            return "Flow navigation not allowed"
    
    def _handle_default(self, action):
        """Handle default sequencing"""
        return f"Default sequencing for action: {action}"
    
    def _is_activity_available(self):
        """Check if activity is available"""
        # Check if activity is not hidden
        if self.activity_state.raw_data.get('hidden', False):
            return False
        
        # Check if activity is not disabled
        if self.activity_state.raw_data.get('disabled', False):
            return False
        
        return True
    
    def _check_prerequisites(self):
        """Check prerequisites for activity"""
        try:
            prerequisites = self.sequencing.prerequisites or {}
            
            if not prerequisites:
                return True, "No prerequisites"
            
            # Check prerequisite activities
            prerequisite_activities = prerequisites.get('activities', [])
            for prereq_activity in prerequisite_activities:
                prereq_result, prereq_message = self._is_prerequisite_satisfied(prereq_activity)
                if not prereq_result:
                    return False, f"Prerequisite not satisfied: {prereq_message}"
            
            return True, "All prerequisites satisfied"
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error checking prerequisites: {e}")
            return False, f"Prerequisite error: {str(e)}"
    
    def _is_prerequisite_satisfied(self, prereq_activity):
        """Check if prerequisite activity is satisfied"""
        try:
            prereq_state = SCORM2004ActivityState.objects.get(
                activity_id=prereq_activity['id'],
                learner=self.learner,
                registration_id=self.registration_id
            )
            
            # Check completion
            if prereq_activity.get('completion_required', False):
                if prereq_state.completion_status != 'completed':
                    return False, f"Prerequisite {prereq_activity['id']} not completed"
            
            # Check success
            if prereq_activity.get('success_required', False):
                if prereq_state.success_status != 'passed':
                    return False, f"Prerequisite {prereq_activity['id']} not passed"
            
            # Check score
            if prereq_activity.get('score_required'):
                if prereq_state.score_scaled < prereq_activity['score_required']:
                    return False, f"Prerequisite {prereq_activity['id']} score too low"
            
            return True, f"Prerequisite {prereq_activity['id']} satisfied"
            
        except SCORM2004ActivityState.DoesNotExist:
            return False, f"Prerequisite {prereq_activity['id']} not attempted"
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error checking prerequisite: {e}")
            return False, f"Prerequisite error: {str(e)}"
    
    def _check_objective_satisfaction(self):
        """Check objective satisfaction"""
        try:
            objectives = self.sequencing.objectives or {}
            
            if not objectives:
                return True, "No objectives"
            
            # Check if objectives are satisfied
            for objective_id, objective_data in objectives.items():
                objective_result, objective_message = self._is_objective_satisfied(objective_id, objective_data)
                if not objective_result:
                    return False, f"Objective not satisfied: {objective_message}"
            
            return True, "All objectives satisfied"
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error checking objectives: {e}")
            return False, f"Objective error: {str(e)}"
    
    def _is_objective_satisfied(self, objective_id, objective_data):
        """Check if objective is satisfied"""
        try:
            objective_state = self.activity_state.objectives.get(objective_id, {})
            
            # Check completion
            if objective_data.get('completion_required', False):
                if objective_state.get('completion_status') != 'completed':
                    return False, f"Objective {objective_id} not completed"
            
            # Check success
            if objective_data.get('success_required', False):
                if objective_state.get('success_status') != 'passed':
                    return False, f"Objective {objective_id} not passed"
            
            return True, f"Objective {objective_id} satisfied"
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error checking objective {objective_id}: {e}")
            return False, f"Objective error: {str(e)}"
    
    def _is_forward_navigation(self, target):
        """Check if navigation is forward"""
        # Simple implementation - in real system would check activity tree
        return True
    
    def _navigate_to_target(self, target):
        """Navigate to target activity"""
        if target:
            # Update current activity
            self.activity_state.raw_data['current_activity'] = target
            self.activity_state.save()
            return f"Navigated to {target}"
        return "Navigation completed"
    
    def _navigate_flow(self, target=None):
        """Navigate using flow sequencing"""
        flow_rules = self.sequencing.sequencing_rules.get('flow', {})
        
        if target:
            return self._navigate_to_target(target)
        
        # Auto-flow to next activity
        next_activity = self._get_next_activity()
        if next_activity:
            return self._navigate_to_target(next_activity)
        
        return "Flow navigation completed"
    
    def _get_next_activity(self):
        """Get next activity in flow"""
        # Simple implementation - in real system would use activity tree
        return None
    
    def _rollup_completion(self):
        """Rollup completion status"""
        rollup_rules = self.sequencing.rollup_rules or {}
        
        # Check if all children are completed
        children_completed = self._check_children_completion()
        
        if children_completed and rollup_rules.get('completion_rollup', {}).get('enabled', False):
            self.activity_state.completion_status = 'completed'
            self.activity_state.save()
    
    def _rollup_objectives(self):
        """Rollup objective status"""
        rollup_rules = self.sequencing.rollup_rules or {}
        
        # Check if objectives are satisfied
        objectives_satisfied = self._check_objectives_satisfied()
        
        if objectives_satisfied and rollup_rules.get('objective_rollup', {}).get('enabled', False):
            # Update objective status
            for objective_id in self.activity_state.objectives:
                self.activity_state.objectives[objective_id]['completion_status'] = 'completed'
            self.activity_state.save()
    
    def _rollup_progress(self):
        """Rollup progress measure"""
        rollup_rules = self.sequencing.rollup_rules or {}
        
        # Calculate progress from children
        children_progress = self._calculate_children_progress()
        
        if rollup_rules.get('progress_rollup', {}).get('enabled', False):
            self.activity_state.progress_measure = children_progress
            self.activity_state.save()
    
    def _check_children_completion(self):
        """Check if all children are completed"""
        # Enhanced implementation with proper activity tree checking
        try:
            # Get child activities from sequencing rules
            children = self.sequencing.sequencing_rules.get('children', [])
            if not children:
                return True
            
            # Check each child's completion status
            for child_id in children:
                try:
                    child_state = SCORM2004ActivityState.objects.get(
                        activity_id=child_id,
                        learner=self.learner,
                        registration_id=self.registration_id
                    )
                    if child_state.completion_status != 'completed':
                        return False
                except SCORM2004ActivityState.DoesNotExist:
                    # Child not attempted yet
                    return False
            
            return True
        except Exception as e:
            # Log error and return safe default
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error checking children completion: {e}")
            return False
    
    def _check_objectives_satisfied(self):
        """Check if objectives are satisfied"""
        objectives = self.activity_state.objectives or {}
        
        for objective_id, objective_data in objectives.items():
            if objective_data.get('completion_status') != 'completed':
                return False
        
        return True
    
    def _calculate_children_progress(self):
        """Calculate progress from children activities"""
        try:
            # Get child activities from sequencing rules
            children = self.sequencing.sequencing_rules.get('children', [])
            if not children:
                return 1.0
            
            total_progress = 0.0
            completed_children = 0
            
            # Calculate progress from each child
            for child_id in children:
                try:
                    child_state = SCORM2004ActivityState.objects.get(
                        activity_id=child_id,
                        learner=self.learner,
                        registration_id=self.registration_id
                    )
                    
                    # Get child's progress measure
                    child_progress = child_state.progress_measure or 0.0
                    total_progress += child_progress
                    
                    if child_state.completion_status == 'completed':
                        completed_children += 1
                        
                except SCORM2004ActivityState.DoesNotExist:
                    # Child not attempted yet, count as 0 progress
                    pass
            
            # Calculate average progress
            if children:
                return total_progress / len(children)
            else:
                return 1.0
                
        except Exception as e:
            # Log error and return safe default
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error calculating children progress: {e}")
            return 0.0
    
    def _update_activity_state(self, action, target):
        """Update activity state based on action"""
        with transaction.atomic():
            # Update timestamps
            if not self.activity_state.first_launch:
                self.activity_state.first_launch = django_timezone.now()
            self.activity_state.last_launch = django_timezone.now()
            
            # Update raw data
            self.activity_state.raw_data['last_action'] = action
            self.activity_state.raw_data['last_target'] = target
            self.activity_state.raw_data['last_update'] = django_timezone.now().isoformat()
            
            # Update completion if applicable
            if action == 'completed':
                self.activity_state.completion_status = 'completed'
                self.activity_state.completion_date = django_timezone.now()
            
            # Update success if applicable
            if action == 'passed':
                self.activity_state.success_status = 'passed'
            
            self.activity_state.save()
    
    def get_sequencing_state(self):
        """Get current sequencing state"""
        return {
            'activity_id': self.activity_id,
            'sequencing_rules': self.sequencing.sequencing_rules,
            'rollup_rules': self.sequencing.rollup_rules,
            'navigation_rules': self.sequencing.navigation_rules,
            'objectives': self.sequencing.objectives,
            'prerequisites': self.sequencing.prerequisites,
            'activity_state': {
                'completion_status': self.activity_state.completion_status,
                'success_status': self.activity_state.success_status,
                'progress_measure': self.activity_state.progress_measure,
                'objectives': self.activity_state.objectives,
                'interactions': self.activity_state.interactions,
                'raw_data': self.activity_state.raw_data
            }
        }
    
    def set_sequencing_rules(self, rules):
        """Set sequencing rules"""
        self.sequencing.sequencing_rules = rules
        self.sequencing.save()
    
    def set_rollup_rules(self, rules):
        """Set rollup rules"""
        self.sequencing.rollup_rules = rules
        self.sequencing.save()
    
    def set_navigation_rules(self, rules):
        """Set navigation rules"""
        self.sequencing.navigation_rules = rules
        self.sequencing.save()
    
    def set_objectives(self, objectives):
        """Set objectives"""
        self.sequencing.objectives = objectives
        self.sequencing.save()
    
    def set_prerequisites(self, prerequisites):
        """Set prerequisites"""
        self.sequencing.prerequisites = prerequisites
        self.sequencing.save()
