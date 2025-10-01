"""
Model Relationship Optimizer
Provides utilities for optimizing database model relationships and cascade handling
"""

from django.db import models
from django.core.exceptions import ValidationError
import logging

logger = logging.getLogger(__name__)

class ModelRelationshipOptimizer:
    """
    Utility class for optimizing model relationships and cascade handling
    """
    
    @staticmethod
    def optimize_foreign_keys(model_class):
        """
        Optimize foreign key relationships for a model class
        
        Args:
            model_class: Django model class to optimize
        """
        optimizations = []
        
        for field in model_class._meta.get_fields():
            if isinstance(field, models.ForeignKey):
                optimization = ModelRelationshipOptimizer._optimize_foreign_key(field)
                if optimization:
                    optimizations.append(optimization)
        
        return optimizations
    
    @staticmethod
    def _optimize_foreign_key(field):
        """
        Optimize a single foreign key field
        
        Args:
            field: ForeignKey field to optimize
            
        Returns:
            dict: Optimization recommendations
        """
        recommendations = []
        
        # Check for missing indexes
        if not field.db_index:
            recommendations.append({
                'type': 'add_index',
                'field': field.name,
                'reason': 'Foreign key should be indexed for better query performance'
            })
        
        # Check for appropriate on_delete behavior
        if field.remote_field.on_delete == models.CASCADE:
            # Check if CASCADE is appropriate
            if hasattr(field.remote_field.model, '_meta') and field.remote_field.model._meta.app_label == 'users':
                if field.name in ['user', 'created_by', 'updated_by']:
                    recommendations.append({
                        'type': 'change_on_delete',
                        'field': field.name,
                        'current': 'CASCADE',
                        'recommended': 'SET_NULL',
                        'reason': 'User-related fields should use SET_NULL to preserve data when user is deleted'
                    })
        
        # Check for missing related_name
        if not field.related_name:
            recommendations.append({
                'type': 'add_related_name',
                'field': field.name,
                'recommended': f'{field.model._meta.model_name}_set',
                'reason': 'Related name improves reverse relationship queries'
            })
        
        return {
            'field': field.name,
            'recommendations': recommendations
        } if recommendations else None
    
    @staticmethod
    def validate_cascade_relationships(model_class):
        """
        Validate cascade relationships to prevent data loss
        
        Args:
            model_class: Django model class to validate
            
        Returns:
            list: Validation issues found
        """
        issues = []
        
        for field in model_class._meta.get_fields():
            if isinstance(field, models.ForeignKey):
                issue = ModelRelationshipOptimizer._validate_foreign_key_cascade(field)
                if issue:
                    issues.append(issue)
        
        return issues
    
    @staticmethod
    def _validate_foreign_key_cascade(field):
        """
        Validate cascade behavior for a foreign key field
        
        Args:
            field: ForeignKey field to validate
            
        Returns:
            dict: Validation issue if found
        """
        # Check for potentially dangerous CASCADE relationships
        if field.remote_field.on_delete == models.CASCADE:
            # Check if this could cause data loss
            if hasattr(field.remote_field.model, '_meta'):
                related_model = field.remote_field.model
                
                # Check if related model is a core model that shouldn't be deleted
                if related_model._meta.app_label in ['users', 'courses', 'branches']:
                    if field.name in ['user', 'created_by', 'updated_by', 'instructor', 'student']:
                        return {
                            'field': field.name,
                            'issue': 'dangerous_cascade',
                            'severity': 'high',
                            'description': f'CASCADE delete on {field.name} could cause data loss',
                            'recommendation': 'Consider using SET_NULL or PROTECT instead'
                        }
        
        return None
    
    @staticmethod
    def get_relationship_summary(model_class):
        """
        Get a summary of all relationships for a model
        
        Args:
            model_class: Django model class to analyze
            
        Returns:
            dict: Relationship summary
        """
        summary = {
            'model': model_class.__name__,
            'foreign_keys': [],
            'many_to_many': [],
            'one_to_one': [],
            'reverse_foreign_keys': [],
            'reverse_many_to_many': [],
            'reverse_one_to_one': []
        }
        
        # Analyze direct relationships
        for field in model_class._meta.get_fields():
            if isinstance(field, models.ForeignKey):
                summary['foreign_keys'].append({
                    'name': field.name,
                    'to': field.remote_field.model.__name__,
                    'on_delete': field.remote_field.on_delete.__name__,
                    'related_name': field.related_name,
                    'null': field.null,
                    'blank': field.blank
                })
            elif isinstance(field, models.ManyToManyField):
                summary['many_to_many'].append({
                    'name': field.name,
                    'to': field.remote_field.model.__name__,
                    'related_name': field.related_name,
                    'through': field.through.__name__ if field.through else None
                })
            elif isinstance(field, models.OneToOneField):
                summary['one_to_one'].append({
                    'name': field.name,
                    'to': field.remote_field.model.__name__,
                    'on_delete': field.remote_field.on_delete.__name__,
                    'related_name': field.related_name
                })
        
        return summary
    
    @staticmethod
    def optimize_queries(model_class, queryset):
        """
        Optimize queries for a model using select_related and prefetch_related
        
        Args:
            model_class: Django model class
            queryset: QuerySet to optimize
            
        Returns:
            QuerySet: Optimized QuerySet
        """
        # Get all foreign key fields
        foreign_keys = [f.name for f in model_class._meta.get_fields() 
                       if isinstance(f, models.ForeignKey)]
        
        # Get all many-to-many fields
        many_to_many = [f.name for f in model_class._meta.get_fields() 
                       if isinstance(f, models.ManyToManyField)]
        
        # Apply select_related for foreign keys
        if foreign_keys:
            queryset = queryset.select_related(*foreign_keys)
        
        # Apply prefetch_related for many-to-many fields
        if many_to_many:
            queryset = queryset.prefetch_related(*many_to_many)
        
        return queryset
    
    @staticmethod
    def create_relationship_indexes(model_class):
        """
        Create database indexes for foreign key relationships
        
        Args:
            model_class: Django model class to create indexes for
            
        Returns:
            list: Index creation SQL statements
        """
        indexes = []
        
        for field in model_class._meta.get_fields():
            if isinstance(field, models.ForeignKey) and not field.db_index:
                index_name = f"{model_class._meta.db_table}_{field.name}_idx"
                indexes.append({
                    'name': index_name,
                    'table': model_class._meta.db_table,
                    'column': field.column,
                    'sql': f"CREATE INDEX {index_name} ON {model_class._meta.db_table} ({field.column});"
                })
        
        return indexes


def optimize_model_relationships():
    """
    Main function to optimize all model relationships in the project
    """
    from django.apps import apps
    
    all_models = apps.get_models()
    optimization_report = {
        'models_analyzed': 0,
        'optimizations_found': 0,
        'issues_found': 0,
        'recommendations': []
    }
    
    for model in all_models:
        optimization_report['models_analyzed'] += 1
        
        # Get optimizations
        optimizations = ModelRelationshipOptimizer.optimize_foreign_keys(model)
        optimization_report['optimizations_found'] += len(optimizations)
        
        # Get validation issues
        issues = ModelRelationshipOptimizer.validate_cascade_relationships(model)
        optimization_report['issues_found'] += len(issues)
        
        if optimizations or issues:
            optimization_report['recommendations'].append({
                'model': model.__name__,
                'optimizations': optimizations,
                'issues': issues
            })
    
    return optimization_report
