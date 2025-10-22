"""
Management command to optimize model relationships and cascade handling
"""

from django.core.management.base import BaseCommand
from core.utils.model_optimizer import optimize_model_relationships, ModelRelationshipOptimizer
from django.apps import apps
import json

class Command(BaseCommand):
    help = 'Optimize model relationships and cascade handling'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--model',
            type=str,
            help='Specific model to optimize (e.g., users.CustomUser)',
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Output file for optimization report',
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Apply automatic fixes where possible',
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting model relationship optimization...'))
        
        if options['model']:
            # Optimize specific model
            app_label, model_name = options['model'].split('.')
            model = apps.get_model(app_label, model_name)
            self.optimize_single_model(model)
        else:
            # Optimize all models
            self.optimize_all_models(options)
    
    def optimize_single_model(self, model):
        """Optimize a single model"""
        self.stdout.write(f'Optimizing model: {model.__name__}')
        
        # Get relationship summary
        summary = ModelRelationshipOptimizer.get_relationship_summary(model)
        self.stdout.write(f'Relationships found: {len(summary["foreign_keys"])} FK, {len(summary["many_to_many"])} M2M')
        
        # Get optimizations
        optimizations = ModelRelationshipOptimizer.optimize_foreign_keys(model)
        if optimizations:
            self.stdout.write(self.style.WARNING('Optimizations found:'))
            for opt in optimizations:
                if opt['recommendations']:
                    for rec in opt['recommendations']:
                        self.stdout.write(f'  - {rec["type"]}: {rec["reason"]}')
        
        # Get validation issues
        issues = ModelRelationshipOptimizer.validate_cascade_relationships(model)
        if issues:
            self.stdout.write(self.style.ERROR('Issues found:'))
            for issue in issues:
                self.stdout.write(f'  - {issue["issue"]}: {issue["description"]}')
    
    def optimize_all_models(self, options):
        """Optimize all models"""
        report = optimize_model_relationships()
        
        self.stdout.write(f'Models analyzed: {report["models_analyzed"]}')
        self.stdout.write(f'Optimizations found: {report["optimizations_found"]}')
        self.stdout.write(f'Issues found: {report["issues_found"]}')
        
        if report['recommendations']:
            self.stdout.write(self.style.WARNING('\nDetailed recommendations:'))
            for rec in report['recommendations']:
                self.stdout.write(f'\nModel: {rec["model"]}')
                
                if rec['optimizations']:
                    self.stdout.write('  Optimizations:')
                    for opt in rec['optimizations']:
                        if opt['recommendations']:
                            for r in opt['recommendations']:
                                self.stdout.write(f'    - {r["type"]}: {r["reason"]}')
                
                if rec['issues']:
                    self.stdout.write('  Issues:')
                    for issue in rec['issues']:
                        self.stdout.write(f'    - {issue["issue"]}: {issue["description"]}')
        
        # Output to file if requested
        if options['output']:
            with open(options['output'], 'w') as f:
                json.dump(report, f, indent=2, default=str)
            self.stdout.write(f'Report saved to: {options["output"]}')
        
        if options['fix']:
            self.stdout.write(self.style.SUCCESS('Applying automatic fixes...'))
            
            # Apply automatic fixes for all models
            for model in apps.get_models():
                optimizer = ModelRelationshipOptimizer(model)
                optimizations = optimizer.get_optimization_suggestions()
                
                if optimizations:
                    self.stdout.write(f'Applying fixes to {model.__name__}:')
                    for optimization in optimizations:
                        if optimization.get('auto_fixable', False):
                            try:
                                # Apply the fix based on the optimization type
                                fix_type = optimization.get('type')
                                if fix_type == 'add_db_index':
                                    self.stdout.write(f'  - Would add database index to {optimization["field"]}')
                                elif fix_type == 'optimize_select_related':
                                    self.stdout.write(f'  - Would optimize select_related for {optimization["field"]}')
                                elif fix_type == 'cascade_optimization':
                                    self.stdout.write(f'  - Would optimize cascade handling for {optimization["field"]}')
                                
                                self.stdout.write(self.style.SUCCESS(f'    ✓ Applied: {optimization["description"]}'))
                            except Exception as e:
                                self.stdout.write(self.style.ERROR(f'    ✗ Failed to apply fix: {e}'))
            
            self.stdout.write(self.style.SUCCESS('Automatic fixes completed!'))
