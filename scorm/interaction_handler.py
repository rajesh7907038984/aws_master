# -*- coding: utf-8 -*-
"""
SCORM Interaction Handler
Handles detailed interaction tracking and database storage
"""
import json
import logging
from datetime import datetime
from decimal import Decimal
from django.utils import timezone
from .models import ScormInteraction, ScormObjective, ScormComment

logger = logging.getLogger(__name__)


class ScormInteractionHandler:
    """
    Handler for SCORM interaction data storage and retrieval
    """
    
    def __init__(self, attempt):
        self.attempt = attempt
    
    def save_interaction(self, interaction_data):
        """
        Save interaction data to database
        
        Args:
            interaction_data (dict): Interaction data from SCORM API
        """
        try:
            interaction_id = interaction_data.get('id', '')
            if not interaction_id:
                logger.warning("No interaction ID provided")
                return None
            
            # Get or create interaction
            interaction, created = ScormInteraction.objects.get_or_create(
                attempt=self.attempt,
                interaction_id=interaction_id,
                defaults={
                    'interaction_type': interaction_data.get('type', 'other'),
                    'description': interaction_data.get('description', ''),
                    'student_response': interaction_data.get('student_response', ''),
                    'correct_response': interaction_data.get('correct_response', ''),
                    'result': interaction_data.get('result', ''),
                    'weighting': self._parse_decimal(interaction_data.get('weighting')),
                    'score_raw': self._parse_decimal(interaction_data.get('score_raw')),
                    'timestamp': self._parse_timestamp(interaction_data.get('timestamp')),
                    'latency': interaction_data.get('latency', ''),
                    'objectives': interaction_data.get('objectives', []),
                    'learner_response_data': interaction_data.get('learner_response_data', {})
                }
            )
            
            if not created:
                # Update existing interaction
                interaction.interaction_type = interaction_data.get('type', interaction.interaction_type)
                interaction.description = interaction_data.get('description', interaction.description)
                interaction.student_response = interaction_data.get('student_response', interaction.student_response)
                interaction.correct_response = interaction_data.get('correct_response', interaction.correct_response)
                interaction.result = interaction_data.get('result', interaction.result)
                interaction.weighting = self._parse_decimal(interaction_data.get('weighting')) or interaction.weighting
                interaction.score_raw = self._parse_decimal(interaction_data.get('score_raw')) or interaction.score_raw
                interaction.timestamp = self._parse_timestamp(interaction_data.get('timestamp')) or interaction.timestamp
                interaction.latency = interaction_data.get('latency', interaction.latency)
                interaction.objectives = interaction_data.get('objectives', interaction.objectives)
                interaction.learner_response_data = interaction_data.get('learner_response_data', interaction.learner_response_data)
                interaction.save()
            
            logger.info(f"Saved interaction {interaction_id} for attempt {self.attempt.id}")
            return interaction
            
        except Exception as e:
            logger.error(f"Error saving interaction: {str(e)}")
            return None
    
    def save_objective(self, objective_data):
        """
        Save objective data to database
        
        Args:
            objective_data (dict): Objective data from SCORM API
        """
        try:
            objective_id = objective_data.get('id', '')
            if not objective_id:
                logger.warning("No objective ID provided")
                return None
            
            # Get or create objective
            objective, created = ScormObjective.objects.get_or_create(
                attempt=self.attempt,
                objective_id=objective_id,
                defaults={
                    'description': objective_data.get('description', ''),
                    'success_status': objective_data.get('success_status', 'not attempted'),
                    'completion_status': objective_data.get('completion_status', 'not attempted'),
                    'score_raw': self._parse_decimal(objective_data.get('score_raw')),
                    'score_min': self._parse_decimal(objective_data.get('score_min')),
                    'score_max': self._parse_decimal(objective_data.get('score_max')),
                    'score_scaled': self._parse_decimal(objective_data.get('score_scaled')),
                    'progress_measure': self._parse_decimal(objective_data.get('progress_measure')),
                    'objective_data': objective_data.get('objective_data', {})
                }
            )
            
            if not created:
                # Update existing objective
                objective.description = objective_data.get('description', objective.description)
                objective.success_status = objective_data.get('success_status', objective.success_status)
                objective.completion_status = objective_data.get('completion_status', objective.completion_status)
                objective.score_raw = self._parse_decimal(objective_data.get('score_raw')) or objective.score_raw
                objective.score_min = self._parse_decimal(objective_data.get('score_min')) or objective.score_min
                objective.score_max = self._parse_decimal(objective_data.get('score_max')) or objective.score_max
                objective.score_scaled = self._parse_decimal(objective_data.get('score_scaled')) or objective.score_scaled
                objective.progress_measure = self._parse_decimal(objective_data.get('progress_measure')) or objective.progress_measure
                objective.objective_data = objective_data.get('objective_data', objective.objective_data)
                objective.save()
            
            logger.info(f"Saved objective {objective_id} for attempt {self.attempt.id}")
            return objective
            
        except Exception as e:
            logger.error(f"Error saving objective: {str(e)}")
            return None
    
    def save_comment(self, comment_data):
        """
        Save comment data to database
        
        Args:
            comment_data (dict): Comment data from SCORM API
        """
        try:
            comment_type = comment_data.get('type', 'learner')
            comment_text = comment_data.get('comment', '')
            
            if not comment_text:
                logger.warning("No comment text provided")
                return None
            
            comment = ScormComment.objects.create(
                attempt=self.attempt,
                comment_type=comment_type,
                comment_text=comment_text,
                location=comment_data.get('location', ''),
                timestamp=self._parse_timestamp(comment_data.get('timestamp')),
                comment_data=comment_data.get('comment_data', {})
            )
            
            logger.info(f"Saved {comment_type} comment for attempt {self.attempt.id}")
            return comment
            
        except Exception as e:
            logger.error(f"Error saving comment: {str(e)}")
            return None
    
    def get_interactions(self):
        """Get all interactions for this attempt"""
        return ScormInteraction.objects.filter(attempt=self.attempt).order_by('timestamp', 'created_at')
    
    def get_objectives(self):
        """Get all objectives for this attempt"""
        return ScormObjective.objects.filter(attempt=self.attempt).order_by('created_at')
    
    def get_comments(self):
        """Get all comments for this attempt"""
        return ScormComment.objects.filter(attempt=self.attempt).order_by('timestamp', 'created_at')
    
    def get_interaction_summary(self):
        """Get summary statistics for interactions"""
        interactions = self.get_interactions()
        
        summary = {
            'total_interactions': interactions.count(),
            'correct_interactions': interactions.filter(result='correct').count(),
            'incorrect_interactions': interactions.filter(result='incorrect').count(),
            'interaction_types': {},
            'average_latency': 0,
            'total_score': 0
        }
        
        # Calculate interaction type distribution
        for interaction in interactions:
            interaction_type = interaction.interaction_type
            if interaction_type not in summary['interaction_types']:
                summary['interaction_types'][interaction_type] = 0
            summary['interaction_types'][interaction_type] += 1
        
        # Calculate average latency
        latencies = [interaction.get_latency_seconds() for interaction in interactions if interaction.get_latency_seconds()]
        if latencies:
            summary['average_latency'] = sum(latencies) / len(latencies)
        
        # Calculate total score
        scores = [float(interaction.score_raw) for interaction in interactions if interaction.score_raw]
        if scores:
            summary['total_score'] = sum(scores)
        
        return summary
    
    def _parse_decimal(self, value):
        """Parse decimal value safely"""
        if value is None or value == '':
            return None
        try:
            return Decimal(str(value))
        except (ValueError, TypeError):
            return None
    
    def _parse_timestamp(self, value):
        """Parse timestamp value safely"""
        if not value:
            return None
        try:
            # Handle ISO 8601 format
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            return value
        except (ValueError, TypeError):
            return None


class ScormInteractionAnalyzer:
    """
    Analyzer for SCORM interaction data
    """
    
    def __init__(self, attempt):
        self.attempt = attempt
        self.handler = ScormInteractionHandler(attempt)
    
    def analyze_learner_performance(self):
        """Analyze learner performance across interactions"""
        interactions = self.handler.get_interactions()
        objectives = self.handler.get_objectives()
        
        analysis = {
            'attempt_id': self.attempt.id,
            'user_id': self.attempt.user.id,
            'scorm_package_id': self.attempt.scorm_package.id,
            'interaction_analysis': self._analyze_interactions(interactions),
            'objective_analysis': self._analyze_objectives(objectives),
            'overall_performance': self._calculate_overall_performance(interactions, objectives)
        }
        
        return analysis
    
    def _analyze_interactions(self, interactions):
        """Analyze interaction data"""
        if not interactions.exists():
            return {'message': 'No interactions found'}
        
        analysis = {
            'total_count': interactions.count(),
            'correct_count': interactions.filter(result='correct').count(),
            'incorrect_count': interactions.filter(result='incorrect').count(),
            'accuracy_rate': 0,
            'interaction_types': {},
            'difficulty_analysis': {},
            'timing_analysis': {}
        }
        
        # Calculate accuracy rate
        if analysis['total_count'] > 0:
            analysis['accuracy_rate'] = (analysis['correct_count'] / analysis['total_count']) * 100
        
        # Analyze by interaction type
        for interaction in interactions:
            interaction_type = interaction.interaction_type
            if interaction_type not in analysis['interaction_types']:
                analysis['interaction_types'][interaction_type] = {
                    'total': 0,
                    'correct': 0,
                    'incorrect': 0
                }
            
            analysis['interaction_types'][interaction_type]['total'] += 1
            if interaction.result == 'correct':
                analysis['interaction_types'][interaction_type]['correct'] += 1
            elif interaction.result == 'incorrect':
                analysis['interaction_types'][interaction_type]['incorrect'] += 1
        
        # Calculate accuracy by type
        for interaction_type, data in analysis['interaction_types'].items():
            if data['total'] > 0:
                data['accuracy_rate'] = (data['correct'] / data['total']) * 100
        
        return analysis
    
    def _analyze_objectives(self, objectives):
        """Analyze objective data"""
        if not objectives.exists():
            return {'message': 'No objectives found'}
        
        analysis = {
            'total_count': objectives.count(),
            'passed_count': objectives.filter(success_status='passed').count(),
            'failed_count': objectives.filter(success_status='failed').count(),
            'completion_rate': 0,
            'average_score': 0
        }
        
        # Calculate completion rate
        if analysis['total_count'] > 0:
            analysis['completion_rate'] = (analysis['passed_count'] / analysis['total_count']) * 100
        
        # Calculate average score
        scores = [float(obj.score_raw) for obj in objectives if obj.score_raw]
        if scores:
            analysis['average_score'] = sum(scores) / len(scores)
        
        return analysis
    
    def _calculate_overall_performance(self, interactions, objectives):
        """Calculate overall performance metrics"""
        performance = {
            'overall_score': 0,
            'completion_status': 'incomplete',
            'success_status': 'unknown',
            'time_spent': 0,
            'recommendations': []
        }
        
        # Calculate overall score
        if self.attempt.score_raw:
            performance['overall_score'] = float(self.attempt.score_raw)
        
        # Determine completion and success status
        performance['completion_status'] = self.attempt.completion_status
        performance['success_status'] = self.attempt.success_status
        
        # Calculate time spent (convert SCORM time format)
        if self.attempt.total_time:
            performance['time_spent'] = self._parse_scorm_time(self.attempt.total_time)
        
        # Generate recommendations
        if performance['overall_score'] < 70:
            performance['recommendations'].append('Consider reviewing course material')
        
        if interactions.filter(result='incorrect').count() > interactions.count() * 0.5:
            performance['recommendations'].append('Focus on areas with incorrect answers')
        
        return performance
    
    def _parse_scorm_time(self, time_str):
        """Parse SCORM time format to seconds"""
        if not time_str:
            return 0
        
        try:
            # SCORM format: hhhh:mm:ss.ss
            parts = time_str.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                return hours * 3600 + minutes * 60 + seconds
        except (ValueError, IndexError):
            pass
        
        return 0
